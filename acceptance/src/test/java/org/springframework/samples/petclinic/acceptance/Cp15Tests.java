package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp15: collapse repeated internal whitespace in names. */
@Tag("cp15")
class Cp15Tests extends AcceptanceBase {

	@Test
	void coreCollapsesInternalWhitespaceInNames() throws Exception {
		ObjectNode o = validOwner("Mary   Jane", "Van   Dyke");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.firstName").value("Mary Jane"))
				.andExpect(jsonPath("$.lastName").value("Van Dyke"));
	}

	@Test
	void functionalityTrimsAndCollapsesTogether() throws Exception {
		ObjectNode o = validOwner("  Mary   Jane  ", "Smith");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.firstName").value("Mary Jane"));
	}
}
