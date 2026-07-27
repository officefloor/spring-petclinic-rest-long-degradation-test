package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp04: first and last name required and trimmed. */
@Tag("cp04")
class Cp04Tests extends AcceptanceBase {

	@Test
	void coreRejectsMissingFirstName() throws Exception {
		ObjectNode o = validOwner();
		o.remove("firstName");
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void coreRejectsMissingLastName() throws Exception {
		ObjectNode o = validOwner();
		o.remove("lastName");
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void errorRejectsBlankFirstName() throws Exception {
		ObjectNode o = validOwner();
		o.put("firstName", "   ");
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void functionalityTrimsNames() throws Exception {
		ObjectNode o = validOwner("  Alice  ", "  Smith  ");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.firstName").value("Alice"))
				.andExpect(jsonPath("$.lastName").value("Smith"));
	}
}
