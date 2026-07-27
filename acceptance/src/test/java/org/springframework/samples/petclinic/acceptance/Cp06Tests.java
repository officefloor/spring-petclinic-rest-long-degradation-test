package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp06: city required; stored title-cased. */
@Tag("cp06")
class Cp06Tests extends AcceptanceBase {

	@Test
	void coreRejectsBlankCity() throws Exception {
		ObjectNode o = validOwner();
		o.put("city", "  ");
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void errorRejectsMissingCity() throws Exception {
		ObjectNode o = validOwner();
		o.remove("city");
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void functionalityStoresCityTitleCased() throws Exception {
		ObjectNode o = validOwner();
		o.put("city", "new york");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.city").value("New York"));
	}

	@Test
	void functionalityLowercasesRemainder() throws Exception {
		ObjectNode o = validOwner();
		o.put("city", "PARIS");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.city").value("Paris"));
	}
}
