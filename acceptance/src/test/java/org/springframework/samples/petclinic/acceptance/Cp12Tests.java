package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** address-normalize: Introduce address normalization applied whenever an owner is created: trim and collapse wh... */
@Tag("cp12")
class Cp12Tests extends AcceptanceBase {

	@Test
	void coreNormalizesWhitespaceAndCase() throws Exception {
		ObjectNode o = ownerNode();
		o.put("address", "  12  main  st ");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.address").value("12 MAIN STREET"));
	}

	@Test
	void functionalityExpandsAbbreviations() throws Exception {
		ObjectNode o = ownerNode();
		o.put("address", "7 elm ave");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.address").value("7 ELM AVENUE"));
	}

	@Test
	void errorRejectsBlankAfterNormalize() throws Exception {
		ObjectNode o = ownerNode();
		o.put("address", "   ");
		createOwner(o).andExpect(status().isBadRequest());
	}
}
